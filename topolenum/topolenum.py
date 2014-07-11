import copy,math
from sys import stderr
from collections import defaultdict
from StringIO import StringIO
from Bio.Phylo.BaseTree import Tree, Clade
from .tree import T

def check_against_histograms(extensions,pwhistdict,freq_cutoff=0.01):
    good_extensions = {}
    if all(any(isinstance(f,str) for f in ext) for ext in extensions):
        for att,pairs in extensions.items():
            already_passed = [p[0] for p in pairs]
            distance_pieces = [{ln:len(c.get_path(ln)) for ln in T(c).leaf_names} for c in att if not isinstance(c,str)].pop()
            new_leaf = [c for c in att if isinstance(c,str)].pop()
            distances = {frozenset({f,new_leaf}):d+1 for f,d in distance_pieces.items()}
            if all((d in pwhistdict[p] and pwhistdict[p][d] > freq_cutoff) for p,d in distances.items()):
                good_extensions[att] = pairs
    else:
        for j,pairs in extensions.items():
            already_passed = [p[0] for p in pairs]
            distance_pieces = [{ln:len(c.get_path(ln)) for ln in T(c).leaf_names} for c in j]
            distances = {frozenset({f1,f2}):distance_pieces[0][f1]+distance_pieces[1][f2]+1
                         for f1 in distance_pieces[0] for f2 in distance_pieces[1] if frozenset({f1,f2}) not in already_passed}
            if all((d in pwhistdict[p] and pwhistdict[p][d] > freq_cutoff) for p,d in distances.items()):
                good_extensions[j] = pairs
    return good_extensions

def find_legal_extensions(built_clades,available_pairs):
    new_pairs = []
    joins = defaultdict(list)
    attachments = defaultdict(list)
    already_connected = {frozenset({ln for ln in T(c).leaf_names}):c for c in built_clades}
    already_connected_flat = frozenset({ln for k in already_connected for ln in k})
    for pair in available_pairs:
      if pair[1][0] == 1:
        new_pairs.append(pair)
      elif pair[0] & already_connected_flat:
          if pair[0] < already_connected_flat:
              if any(pair[0] <= acs for acs in already_connected.keys()):
                  continue
              else:
                  curr_hosts = {f:[c for ls,c in already_connected.items() if f in ls].pop() for f in pair[0]}
                  assert len(curr_hosts) == 2
                  if pair[1][0] == sum(len(c.get_path(f)) for f,c in curr_hosts.items())+1:
                      joins[frozenset({c for c in curr_hosts.values()})].append(pair)
          else:
              curr_host = {f:[c for ls,c in already_connected.items() if f in ls].pop() for f in pair[0] if f in already_connected_flat}
              assert len(curr_host) == 1,str(curr_host)+' ** '+str(pair)
              new_leaf = [f for f in pair[0] if f not in curr_host.keys()].pop()
              if pair[1][0] == sum(len(c.get_path(f)) for f,c in curr_host.items())+1:
                  attachments[frozenset({c for c in curr_host.values()}.union([new_leaf]))].append(pair)
    return new_pairs,joins,attachments
          
def remove_inconsistent_pairs(extension,available_pair_idxs,pairs_master,extension_type=None):
    remove_these = []
    if extension_type == 'new_pair':
        remove_these.extend(filter(lambda x: pairs_master[x][1][0] == 1 and pairs_master[x][0] & extension and not pairs_master[x][0] == extension,available_pair_idxs))
        remove_these.extend(filter(lambda x: pairs_master[x][1][0] > 1 and pairs_master[x][0] == extension,available_pair_idxs))
    else:
        leafsets = [[c] if isinstance(c,str) else T(c).leaf_names for c in extension]
        compare_against = {frozenset({f1,f2}) for f1 in leafsets[0] for f2 in leafsets[1]}
        tmp = [c for c in extension if isinstance(c,str)]
        new_leaf = tmp.pop() if tmp else False
        for i in available_pair_idxs:
            if pairs_master[i][0] in compare_against:
                remove_these.append(i)
            elif new_leaf:
                if new_leaf in pairs_master[i][0] and pairs_master[i][1][0] == 1:
                    remove_these.append(i)
    
    return filter(lambda x: x not in remove_these,available_pair_idxs)

def look_ahead(clades,pwhistdict,curr_partial_score):
    scored_pairs = []
    partial_distances = {}
    for c in clades:
        tc = T(c)
        leafnames = tc.leaf_names
        for i,ln1 in enumerate(leafnames):
            partial_distances[ln1] = len(tc.get_path(ln1))
            for ln2 in leafnames[i+1:]:
                scored_pairs.append(frozenset({ln1,ln2}))
    best_possible_full_score = curr_partial_score
    for k,v in pwhistdict.items():
        if k not in scored_pairs:
            min_dist = sum(partial_distances[f] if f in partial_distances else 0 for f in k)+1
            if [freq for dist,freq in v.items() if dist >= min_dist]:
                best_possible_full_score += math.log(max(freq for dist,freq in v.items() if dist >= min_dist))
            else:
                return None
    return best_possible_full_score

def build_extension(extension,assembly,pairs_master,pwhistdict,extension_type=None):
    if extension_type == 'new_pair':
        assembly[2].pop(assembly[2].index(pairs_master.index(extension)))
        for f in extension[0]:
            assembly[1].pop(assembly[1].index(f))
        assembly[4] += math.log(extension[1][1])
        assembly[0].append(Clade(clades=[Clade(name=f) for f in extension[0]]))
    else:
        for p in extension[1]:
            assembly[2].pop(assembly[2].index(pairs_master.index(p)))
        identified_pairs = dict(extension[1])
        new_leaf = False
        existing_clade_copies = []
        for piece in extension[0]:
            if isinstance(piece,str):
                new_leaf = piece
                assembly[1].pop(assembly[1].index(piece))
            else:
                candidates_for_copy_of_existing_clade = [c for c in assembly[0] if set(T(c).leaf_names) == set(T(piece).leaf_names)]
                assert len(candidates_for_copy_of_existing_clade) == 1
                existing_clade_copies.append(candidates_for_copy_of_existing_clade.pop())
        if new_leaf:
            assert len(existing_clade_copies) == 1
            existing_clade = existing_clade_copies.pop()
            for f in T(existing_clade).leaf_names:
                if frozenset({new_leaf,f}) in identified_pairs:
                    assembly[4] += math.log(identified_pairs[frozenset({new_leaf,f})][1])
                else:
                    assembly[4] += math.log(pwhistdict[frozenset({new_leaf,f})][len(existing_clade.get_path(f))+1])
            assembly[0].pop(assembly[0].index(existing_clade))
            assembly[0].append(Clade(clades=[existing_clade,Clade(name=new_leaf)]))
        else:
            assert len(existing_clade_copies) == 2
            for f1 in T(existing_clade_copies[0]).leaf_names:
                for f2 in T(existing_clade_copies[1]).leaf_names:
                    if frozenset({f1,f2}) in identified_pairs:
                        assembly[4] += math.log(identified_pairs[frozenset({f1,f2})][1])
                    else:
                        assembly[4] += math.log(pwhistdict[frozenset({f1,f2})][len(existing_clade_copies[0].get_path(f1))+len(existing_clade_copies[1].get_path(f2))+1])
            for c in existing_clade_copies:
                assembly[0].pop(assembly[0].index(c))
            assembly[0].append(Clade(clades=existing_clade_copies))
#     assembly[6] = {frozenset({frozenset(n.leaf_names) for n in T(c).get_nonterminals()}) for c in assembly[0]}
    assembly[2] = remove_inconsistent_pairs(extension[0],assembly[2],pairs_master,extension_type)

def build_all_extensions(new_pairs,joins,attachments,assembly,pairs_master,pwhistdict):
    build_here = [assembly]
    build_here.extend(copy.deepcopy(assembly) for i in xrange(sum(len(coll) for coll in [new_pairs,joins,attachments])-1))
    bld_idx = 0
    for np in new_pairs:
        build_extension(np,build_here[bld_idx],pairs_master,pwhistdict,'new_pair')
        bld_idx += 1
    for ext,pairs in joins.items()+attachments.items():
        build_extension((ext,pairs),build_here[bld_idx],pairs_master,pwhistdict)
        bld_idx += 1
    build_here.pop(0)
    return build_here

def assembly_iteration(assemblies,pairs_master,pwhistdict,accepted_assemblies,encountered_leaf_subsets,num_requested_trees,processing_bite_size,iternum):
    new_this_iteration = []
    accepted_this_iteration = []
    discarded_this_iteration = {'u':[],'e':[],'cs':[],'ps':[]}
    assemblies_this_iter = [(i,asb) for i,asb in enumerate(assemblies) if (asb[1] or len(asb[0]) > 1)]
    if len(accepted_assemblies) < num_requested_trees and len(assemblies_this_iter) > num_requested_trees:
#         assemblies_this_iter = sorted(assemblies_this_iter,key=lambda x: (len(x[1][1]),x[1][4]))[:num_requested_trees]
        assemblies_this_iter = sorted(assemblies_this_iter,key=lambda x: (len(x[1][1]),sum((c.count_terminals()+(c.count_terminals()-1))/2
                                                                             for c in x[1][0])/x[1][4]))[:num_requested_trees]
    elif len(accepted_assemblies) >= num_requested_trees:
#         assemblies_this_iter = sorted(assemblies_this_iter,key=lambda x: (len(x[1][1]),x[1][4]))[:processing_bite_size]
        if iternum % 2 == 0:
            assemblies_this_iter = sorted(assemblies_this_iter,key=lambda x: (len(x[1][1]),sum((c.count_terminals()+(c.count_terminals()-1))/2
                                                                                               for c in x[1][0])/x[1][4]))[:processing_bite_size]
        else:
            if iternum % 3 == 0:
                assemblies_this_iter = sorted(assemblies_this_iter,key=lambda x: sum((c.count_terminals()+(c.count_terminals()-1))/2
                                                                                     for c in x[1][0])/x[1][4],reverse=True)[:processing_bite_size/2]
            else:
                assemblies_this_iter = sorted(assemblies_this_iter,key=lambda x: sum((c.count_terminals()+(c.count_terminals()-1))/2
                                                                                       for c in x[1][0])/x[1][4])[:processing_bite_size]
    print >>stderr,len(assemblies),"tracked trees,",len(accepted_assemblies),"accepted, working on",\
                    len(assemblies_this_iter),"this iteration, total of",len(assemblies)-len(accepted_assemblies),"are incomplete"
    assemblies_per_dot = int(math.ceil(float(len(assemblies_this_iter))/50))
    for i,assembly in assemblies_this_iter:
        print >>stderr,'['+'|'*(assemblies_this_iter.index((i,assembly)) % 10)+' '*(9-(assemblies_this_iter.index((i,assembly)) % 10))+']'+\
                        '['+'*'*(assemblies_this_iter.index((i,assembly))/assemblies_per_dot)+' '*(50-assemblies_this_iter.index((i,assembly))/assemblies_per_dot)+']'+\
                        '\taccepted:',len(accepted_this_iteration),'discarded:',sum(len(v) for v in discarded_this_iteration.values()),\
                        "new:",len(new_this_iteration),'\r',
        new_pairs,joins,attachments = find_legal_extensions(assembly[0],[pairs_master[i] for i in assembly[2]])
        good_joins = check_against_histograms(joins,pwhistdict)
        good_attachments = check_against_histograms(attachments,pwhistdict)
        if not new_pairs and not good_joins and not good_attachments:
            discarded_this_iteration['e'].append(assemblies.pop(assemblies.index(assembly)))
            continue
        new_assemblies = build_all_extensions(new_pairs,good_joins,good_attachments,assembly,pairs_master,pwhistdict)
        still_in_play = True
        if len(accepted_assemblies) == num_requested_trees and assembly[4] < accepted_assemblies[-1][4]:
            discarded_this_iteration['cs'].append(assemblies.pop(assemblies.index(assembly)))
            encountered_leaf_subsets.add(frozenset({frozenset({frozenset(n.leaf_names) for n in T(c).get_nonterminals()}) for c in assembly[0]}))
            still_in_play = False
        else:
            la = look_ahead(assembly[0],pwhistdict,assembly[4])
            if la is None:
                discarded_this_iteration['e'].append(assemblies.pop(assemblies.index(assembly)))
                encountered_leaf_subsets.add(frozenset({frozenset({frozenset(n.leaf_names) for n in T(c).get_nonterminals()}) for c in assembly[0]}))
                still_in_play
            elif len(accepted_assemblies) == num_requested_trees and la < accepted_assemblies[-1][4]:
                discarded_this_iteration['ps'].append(assemblies.pop(assemblies.index(assembly)))
                encountered_leaf_subsets.add(frozenset({frozenset({frozenset(n.leaf_names) for n in T(c).get_nonterminals()}) for c in assembly[0]}))
                still_in_play = False
            else:
                leafsets = frozenset({frozenset({frozenset(n.leaf_names) for n in T(c).get_nonterminals()}) for c in assembly[0]})
                if leafsets in encountered_leaf_subsets:
                    discarded_this_iteration['u'].append(assemblies.pop(assemblies.index(assembly)))
                    still_in_play = False
                else:
                    encountered_leaf_subsets.add(leafsets)
    #             for other_assembly in assemblies:
#                 if other_assembly is not assembly:
#                     if assembly[6] == other_assembly[6]:
#                         assert set(assembly[2]) == set(other_assembly[2])
#                         discarded_this_iteration['u'].append(assemblies.pop(assemblies.index(assembly)))
#                         still_in_play = False
#                         break
#             else:
#                 if assembly[6] in encountered_leaf_subsets:
#                     discarded_this_iteration['u'].append(assemblies.pop(assemblies.index(assembly)))
#                     still_in_play = False
        rejected_new_assemblies = []
        for new_assembly in new_assemblies:
            if len(accepted_assemblies) == num_requested_trees and new_assembly[4] < accepted_assemblies[-1][4]:
                rejected_new_assemblies.append(new_assembly)
                encountered_leaf_subsets.add(frozenset({frozenset({frozenset(n.leaf_names) for n in T(c).get_nonterminals()}) for c in new_assembly[0]}))
            else:
                la = look_ahead(new_assembly[0],pwhistdict,new_assembly[4])
                if la is None:
                    rejected_new_assemblies.append(new_assembly)
                    encountered_leaf_subsets.add(frozenset({frozenset({frozenset(n.leaf_names) for n in T(c).get_nonterminals()}) for c in new_assembly[0]}))
                elif len(accepted_assemblies) == num_requested_trees and la < accepted_assemblies[-1][4]:
                    rejected_new_assemblies.append(new_assembly)
                    encountered_leaf_subsets.add(frozenset({frozenset({frozenset(n.leaf_names) for n in T(c).get_nonterminals()}) for c in new_assembly[0]}))
                else:
                    leafsets = frozenset({frozenset({frozenset(n.leaf_names) for n in T(c).get_nonterminals()}) for c in new_assembly[0]})
                    if leafsets in encountered_leaf_subsets:
                        rejected_new_assemblies.append(new_assembly)
                    else:
                        encountered_leaf_subsets.add(leafsets)
    #                 for other_assembly in assemblies:
#                     if new_assembly[6] == other_assembly[6]:
#                         assert set(new_assembly[2]) == set(other_assembly[2])
#                         rejected_new_assemblies.append(new_assembly)
#                         break
#                 else:
#                     if new_assembly[6] in encountered_leaf_subsets:
#                         rejected_new_assemblies.append(new_assembly)
        new_assemblies = filter(lambda x: x not in rejected_new_assemblies,new_assemblies)
        new_this_iteration.extend(new_assemblies)
        assemblies.extend(new_assemblies)
        if still_in_play and len(assembly[0]) == 1 and not assembly[1]:
            accepted_this_iteration.append(assembly)
            accepted_assemblies.append(assembly)
            accepted_assemblies = sorted(accepted_assemblies,key=lambda x: x[4],reverse=True)
            if len(accepted_assemblies) > num_requested_trees:
                assert len(accepted_assemblies)-1 == num_requested_trees
                if accepted_assemblies[-1] in assemblies and accepted_assemblies[-1] not in discarded_this_iteration['cs']:
                    discarded_this_iteration['cs'].append(assemblies.pop(assemblies.index(accepted_assemblies.pop())))
                elif accepted_assemblies[-1] not in discarded_this_iteration['cs']:
                    discarded_this_iteration['cs'].append(accepted_assemblies.pop())
        for new_assembly in new_assemblies:
            if len(new_assembly[0]) == 1 and not new_assembly[1]:
                accepted_this_iteration.append(new_assembly)
                accepted_assemblies.append(new_assembly)
                accepted_assemblies = sorted(accepted_assemblies,key=lambda x: x[4],reverse=True)
                if len(accepted_assemblies) > num_requested_trees:
                    assert len(accepted_assemblies)-1 == num_requested_trees
                    if accepted_assemblies[-1] in assemblies and accepted_assemblies[-1] not in discarded_this_iteration['cs']:
                        discarded_this_iteration['cs'].append(assemblies.pop(assemblies.index(accepted_assemblies.pop())))
                    elif accepted_assemblies[-1] not in discarded_this_iteration['cs']:
                        discarded_this_iteration['cs'].append(accepted_assemblies.pop())
    print >>stderr,' '*110+'\r',
    if new_this_iteration:
        print >>stderr, '\t',len(new_this_iteration),"were added on this iteration"
    if discarded_this_iteration['u']:
        print >>stderr, '\t',len(discarded_this_iteration['u']),"were discarded because they became non-unique"
    if discarded_this_iteration['e']:
        print >>stderr, '\t',len(discarded_this_iteration['e']),"were discarded because there was no way to extend them"
    if discarded_this_iteration['cs']:
        print >>stderr, '\t',len(discarded_this_iteration['cs']),"were discarded because their current score is worse than the worst accepted score"
    if discarded_this_iteration['ps']:
        print >>stderr, '\t',len(discarded_this_iteration['ps']),"were discarded because their best possible final score is worse than the worst accepted score"
    if accepted_this_iteration:
        print >>stderr, '\t',len(accepted_this_iteration),"were completed and accepted on this iteration"
    if accepted_assemblies:
        print >>stderr, '\t'+"Best accepted score is",accepted_assemblies[0][4],"and worst accepted score is",accepted_assemblies[-1][4]
    print >>stderr,'\t',len(encountered_leaf_subsets),"unique leaf sets have been encountered"
    return accepted_assemblies

def assemble_histtrees(pwhist,leaves_to_assemble,num_requested_trees=1000,freq_cutoff=0.9,max_iter=100000,processing_bite_size=10000):
    pwindiv = [(pair[0],score) for pair in [(f,[dd for i,dd in enumerate(ds)
                if sum(ddd[1] for ddd in ds[:i]) < freq_cutoff]) for f,ds in pwhist] for score in pair[1]]
    pairs_master = sorted(pwindiv,key=lambda x: (x[1][0],1-x[1][1]))
    assemblies = [[[],leaves_to_assemble,range(len(pairs_master)),[],0.0]]
    pwhist_as_dicts = {k:dict(v) for k,v in pwhist}
    iterations = 0
    accepted_assemblies = []
    encountered_leaf_subsets = set()
    enough_assemblies_accepted = False
    while any([len(asb[0]) > 1 or asb[1] for asb in assemblies]) and iterations < max_iter:
        new_accepted_assemblies = assembly_iteration(assemblies,pairs_master,pwhist_as_dicts,accepted_assemblies,
                                                 encountered_leaf_subsets,num_requested_trees,processing_bite_size,iterations)
        if new_accepted_assemblies is not accepted_assemblies:
            accepted_assemblies = new_accepted_assemblies
            with open("built_trees.txt",'w') as fh:
                for tree in accepted_assemblies:
                    treestr = StringIO()
                    T(tree[0][0]).write(treestr,'newick')
                    fh.write(str(tree[4])+'\t'+treestr.getvalue())
            print >>stderr, "Accepted assemblies have been updated"
        if not enough_assemblies_accepted and len(accepted_assemblies) >= num_requested_trees:
            assert len(accepted_assemblies) == num_requested_trees
            prev_assemblies_len = len(assemblies)
            assemblies = filter(lambda x: x[4] > accepted_assemblies[-1][4],assemblies)
            print >>stderr,"*** Reached",num_requested_trees,"accepted trees, dumping",prev_assemblies_len-len(assemblies),\
                            "assemblies with scores worse than the worst accepted tree ***"
            enough_assemblies_accepted = True
#         with open("trees_on_iter_"+str(iterations).zfill(2)+'.txt','w') as fh:
#             for asb in sorted(assemblies,key=lambda x: (len(x[1]),-x[4])):
#                 nwkclades = []
#                 for c in asb[0]:
#                     cladestr = StringIO()
#                     T(c).write(cladestr,'newick')
#                     nwkclades.append(cladestr.getvalue().strip().replace(':0.00000',''))
#                 fh.write('>>>'+str(asb[4])+'>>>'+'  '.join(nwkclades)+'\n')
#             print >>stderr,"Wrote current assemblies to file","trees_on_iter_"+str(iterations).zfill(2)+'.txt'
        iterations += 1
    return assemblies,accepted_assemblies
